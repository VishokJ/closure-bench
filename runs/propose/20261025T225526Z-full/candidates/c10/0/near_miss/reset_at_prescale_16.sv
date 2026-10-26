`timescale 1ns / 1ps
// Same path, but reset is sampled when prescale_reg is exactly 16 (start-bit
// countdown), one step below the mid-bit threshold.
module tb;
  logic        clk = 1'b0;
  logic        rst = 1'b1;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b0;
  logic [15:0] prescale = 16'd5;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid;
  wire         busy, overrun_error, frame_error;
  logic        fe_seen = 1'b0;

  always #4 clk = ~clk;

  uart_rx dut (
    .clk(clk), .rst(rst),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error),
    .prescale(prescale)
  );

  always @(posedge clk) if (frame_error) fe_seen = 1'b1;

  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  logic [7:0] b = 8'hA5;

  initial begin
    rst = 1'b1; wait_clks(3);
    rst = 1'b0; wait_clks(10);
    if (busy) $fatal(1, "busy while idle");

    rxd = 1'b0;
    wait_clks(4);   // prescale_reg: 18 -> 17 -> 16; reset sampled at 16
    if (!busy) $fatal(1, "receiver not in frame before reset");

    rst = 1'b1; wait_clks(2);
    if (busy) $fatal(1, "busy not cleared by reset");
    rst = 1'b0;
    wait_clks(1);
    if (busy) $fatal(1, "busy rose too early after reset release");
    wait_clks(1);
    if (!busy) $fatal(1, "busy did not rise on the expected clock");
    wait_clks(38);

    for (int i = 0; i < 8; i++) begin
      rxd = b[i]; wait_clks(40);
    end
    rxd = 1'b1; wait_clks(40);

    if (!m_axis_tvalid) $fatal(1, "no word received after restart");
    if (m_axis_tdata !== 8'hA5) $fatal(1, "wrong data 0x%02h", m_axis_tdata);
    if (fe_seen) $fatal(1, "unexpected frame error");
    m_axis_tready = 1'b1;
    wait_clks(2);
    $display("near miss done");
    $finish;
  end

  initial begin
    #1ms;
    $fatal(1, "timeout");
  end
endmodule
