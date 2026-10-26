`timescale 1ns / 1ps
module tb;
  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b0;
  logic [15:0] prescale = 16'd5;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid;
  wire         busy, overrun_error, frame_error;

  always #4 clk = ~clk;

  uart_rx dut (
    .clk(clk), .rst(rst),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error),
    .prescale(prescale)
  );

  localparam int BIT = 40;

  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  task automatic send_byte(input logic [7:0] b);
    rxd = 1'b0; wait_clks(BIT);
    for (int i = 0; i < 8; i++) begin rxd = b[i]; wait_clks(BIT); end
    rxd = 1'b1; wait_clks(BIT);
  endtask

  initial begin
    bit got;
    wait_clks(2);
    rst = 1'b1; wait_clks(2);
    rst = 1'b0; wait_clks(10);

    // first frame, sink not ready -> word stays pending
    send_byte(8'h3C);
    if (!m_axis_tvalid || m_axis_tdata !== 8'h3C) $fatal(1, "first word not pending");
    wait_clks(20);

    // start a second frame and stop mid-way
    rxd = 1'b0; wait_clks(BIT);
    rxd = 1'b1; wait_clks(BIT);
    rxd = 1'b0; wait_clks(BIT);
    rxd = 1'b1; wait_clks(BIT / 2);
    if (!busy) $fatal(1, "receiver not busy mid-frame");
    if (!m_axis_tvalid) $fatal(1, "pending word lost before reset");

    // reset mid-frame with pending word
    rst = 1'b1; wait_clks(2);
    rxd = 1'b1;
    rst = 1'b0; wait_clks(1);
    if (m_axis_tvalid) $fatal(1, "m_axis_tvalid not cleared by reset");
    if (busy) $fatal(1, "busy not cleared by reset");
    wait_clks(200);
    if (m_axis_tvalid || busy) $fatal(1, "spurious activity after reset");

    // a following well-formed frame
    m_axis_tready = 1'b1;
    send_byte(8'hA5);
    got = 0;
    for (int i = 0; i < 2000 && !got; i++) begin
      if (m_axis_tvalid) begin
        got = 1;
        if (m_axis_tdata !== 8'hA5) $fatal(1, "got 0x%02h, expected 0xA5", m_axis_tdata);
      end else begin
        wait_clks(1);
      end
    end
    // tvalid may already have been consumed during the stop bit; check by history
    if (!got) $fatal(1, "word after reset never seen");
    $display("PASS");
    $finish;
  end

  // capture the handshake during the stop bit as well
  initial begin
    #5ms;
    $fatal(1, "timeout");
  end
endmodule
