`timescale 1ns / 1ps

// Same frame and checks, but prescale = 16'hFFFE (bit 0 cleared): the reload
// is 19'h7FFEF, so the full 19'h7FFF7 value is never reached.
module tb;

  localparam logic [15:0] PRESCALE = 16'hFFFE;
  localparam int BIT = 65534 * 8;

  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b0;
  logic [15:0] prescale = PRESCALE;
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

  int  cyc = 0;
  bit  got = 0;
  int  vcyc = 0;
  logic [7:0] vdata;
  bit  ferr = 0, oerr = 0;

  always @(negedge clk) begin
    cyc = cyc + 1;
    if (m_axis_tvalid && !got) begin
      got = 1;
      vcyc = cyc;
      vdata = m_axis_tdata;
    end
    if (frame_error) ferr = 1;
    if (overrun_error) oerr = 1;
  end

  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  localparam logic [7:0] DATA = 8'hA5;
  int start_cyc;
  int dt;

  initial begin
    wait_clks(2);
    rst = 1'b1; wait_clks(3);
    rst = 1'b0; wait_clks(3);

    start_cyc = cyc;
    rxd = 1'b0; wait_clks(BIT);
    if (busy !== 1'b1) $fatal(1, "receiver not busy during frame");
    for (int i = 0; i < 8; i++) begin
      rxd = DATA[i]; wait_clks(BIT);
    end
    rxd = 1'b1; wait_clks(BIT);
    wait_clks(10);

    if (!got) $fatal(1, "no word received at prescale 0xFFFE");
    if (vdata !== DATA) $fatal(1, "got 0x%02h, expected 0x%02h", vdata, DATA);
    dt = vcyc - start_cyc;
    if (dt < 9 * BIT || dt > 10 * BIT)
      $fatal(1, "tvalid at %0d clocks after start, expected %0d..%0d", dt, 9 * BIT, 10 * BIT);
    if (ferr) $fatal(1, "unexpected frame_error");
    if (oerr) $fatal(1, "unexpected overrun_error");

    m_axis_tready = 1'b1; wait_clks(1);
    m_axis_tready = 1'b0; wait_clks(2);
    if (m_axis_tvalid !== 1'b0) $fatal(1, "tvalid not cleared after handshake");

    $display("near-miss done: 0x%02h received at prescale 0xFFFE", vdata);
    $finish;
  end

  initial begin
    #100ms;
    $fatal(1, "timeout");
  end

endmodule
