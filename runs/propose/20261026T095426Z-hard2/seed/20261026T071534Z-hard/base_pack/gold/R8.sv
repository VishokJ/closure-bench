`timescale 1ns / 1ps
module tb;
  localparam int CLK_PERIOD = 8;

  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b1;
  logic [15:0] prescale = 16'd5;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid;
  wire         busy, overrun_error, frame_error;

  always #(CLK_PERIOD / 2) clk = ~clk;

  uart_rx dut (
    .clk(clk), .rst(rst),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error),
    .prescale(prescale)
  );

  int ngot = 0;
  logic [7:0] got = 8'h00;
  always @(negedge clk) begin
    if (m_axis_tvalid && m_axis_tready) begin
      got = m_axis_tdata;
      ngot++;
    end
  end

  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  task automatic do_reset();
    rst = 1'b0; wait_clks(2);
    rst = 1'b1; wait_clks(2);
    rst = 1'b0; wait_clks(2);
  endtask

  task automatic send_byte(input logic [7:0] b);
    int bit_clks = int'(prescale) * 8;
    rxd = 1'b0; wait_clks(bit_clks);
    for (int i = 0; i < 8; i++) begin
      rxd = b[i]; wait_clks(bit_clks);
    end
    rxd = 1'b1; wait_clks(bit_clks);
  endtask

  initial begin
    do_reset();
    wait_clks(10);
    send_byte(8'hA5);
    wait_clks(5);
    if (ngot != 1 || got !== 8'hA5) $fatal(1, "first word not received: n=%0d got=%02h", ngot, got);
    if (m_axis_tvalid !== 1'b0 || m_axis_tdata !== 8'hA5 || busy !== 1'b0)
      $fatal(1, "bad state after handoff");

    // start bit of the next frame
    rxd = 1'b0;
    wait_clks(20);
    if (busy !== 1'b1 || m_axis_tvalid !== 1'b0 || m_axis_tdata !== 8'hA5)
      $fatal(1, "receiver not busy mid-frame with handed-off word");

    // reset mid-frame, held for two clocks
    rst = 1'b1;
    rxd = 1'b1;
    wait_clks(1);
    if (busy !== 1'b0 || m_axis_tvalid !== 1'b0 || m_axis_tdata !== 8'h00)
      $fatal(1, "reset did not clear outputs: busy=%b tvalid=%b tdata=%02h",
             busy, m_axis_tvalid, m_axis_tdata);
    wait_clks(1);
    if (busy !== 1'b0 || m_axis_tvalid !== 1'b0 || m_axis_tdata !== 8'h00)
      $fatal(1, "outputs not held cleared during reset");
    rst = 1'b0;
    wait_clks(10);
    if (busy !== 1'b0 || m_axis_tvalid !== 1'b0) $fatal(1, "spurious activity after reset");

    // receiver works again after reset
    send_byte(8'h3C);
    wait_clks(5);
    if (ngot != 2 || got !== 8'h3C) $fatal(1, "word after reset wrong: n=%0d got=%02h", ngot, got);

    $display("PASS");
    $finish;
  end

  initial begin
    #10ms;
    $fatal(1, "timeout");
  end
endmodule
